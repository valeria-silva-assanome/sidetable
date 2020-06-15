# -*- coding: utf-8 -*-

import pandas as pd
from pandas.api.types import is_numeric_dtype
import math


@pd.api.extensions.register_dataframe_accessor("stb")
class SideTableAccessor:
    """Pandas dataframe accessor that computes simple summary tables for your data.
    Computes a frequency table on one or more columns with df.stb.freq(['col_name']) 
    Compute a table of missing values with df.stb.missing()
    """
    def __init__(self, pandas_obj):
        self._validate(pandas_obj)
        self._obj = pandas_obj

    @staticmethod
    def _validate(obj):
        # verify this is a DataFrame
        if not isinstance(obj, pd.DataFrame):
            raise AttributeError("Must be a pandas DataFrame")

    def freq(self,
             cols,
             thresh=1,
             other_label='Others',
             clip_0=True,
             value=None,
             style=False):
        """ Create a table that counts the frequency of occurrence or summation of values 
        for one or more columns of data. Table is sorted and includes cumulative
        values which can be useful for identifying a cutoff.

        Example of Titanic df.stb.freq(['class']):
        	        class	Count	Percent	    Cumulative Count	Cumulative Percent
                0	Third	491	    0.551066	491	                0.551066
                1	First	216	    0.242424	707	                0.793490
                2	Second	184	    0.206510	891	                1.000000
        
        Args:
            cols (list):       dataframe column names that will be grouped together
            thresh (float):    all values after this percentage will be combined into a 
                               single category. Default is to not cut any values off 
            other_label (str): if cutoff is used, this text will be used in the dataframe results
            clip_0 (bool):     In cases where 0 counts are generated, remove them from the list
            value (str):       Column that will be summed. If provided, summation is done
                               instead of counting each entry
            style (bool):     Apply a pandas style to format percentages
            
        Returns:
            Dataframe that summarizes the number of occurrences of each value in the provided 
            columns or the sum of the data provided in the value parameter
        """
        if not isinstance(cols, list):
            raise AttributeError('Must pass a list of columns')

        if isinstance(value, list):
            raise AttributeError('value must be a string not a list')

        if value and value not in self._obj.columns:
            raise AttributeError('value must be a column name')

        if value and not is_numeric_dtype(self._obj[value]):
            raise AttributeError(f'{value} must be a numeric column')

        if thresh > 1:
            raise AttributeError('Cutoff must be <= 1.0')

        # Determine aggregation (counts or summation) for each item in column

        # TODO: NaNs need to be handled better. Wait for pandas 1.1
        # https://pandas.pydata.org/pandas-docs/dev/whatsnew/v1.1.0.html#allow-na-in-groupby-key
        if value:
            col_name = value
            agg_func = {value: 'sum'}
            group_data = self._obj.groupby(cols).agg(agg_func).reset_index()
        else:
            col_name = 'Count'
            group_data = self._obj.groupby(cols).size().reset_index(
                name=col_name)

        # Sort the results and cleanup the index
        results = group_data.sort_values(
            [col_name] + cols, ascending=False).reset_index(drop=True)

        # In data with null values, can include 0 counts filter them out by default
        if clip_0:
            results = results[results[col_name] > 0]

        # Include percents
        total = results[col_name].sum()
        results['Percent'] = results[col_name] / total

        # Keep track of cumulative counts or totals as well as their relative percent
        results[f'Cumulative {col_name}'] = results[col_name].cumsum()
        results[f'Cumulative Percent'] = results[f'Cumulative {col_name}'] / total

        # cutoff is a percentage below which all values are grouped together in an
        # others category
        if thresh < 1:
            # Flag the All Other rows
            results['Others'] = False
            results.loc[results[f'Cumulative Percent'] > thresh,
                        'Others'] = True

            # Calculate the total amount and percentage of the others
            other_total = results.loc[results['Others'], col_name].sum()
            other_pct = other_total / total

            # Create the footer row to append to the results
            all_others = pd.DataFrame({
                col_name: [other_total],
                'Percent': [other_pct],
                f'Cumulative {col_name}': [total],
                'Cumulative Percent': [1.0]
            })

            # Add the footer row, remove the Others column and rename the placeholder
            results = results[results['Others'] == False].append(
                all_others, ignore_index=True).drop(columns=['Others']).fillna(
                    dict.fromkeys(cols, other_label))

        if style:
            format_dict = {
                'Percent': '{:.2%}',
                'Cumulative Percent': '{:.2%}',
                'Count': '{0:,.0f}',
                f'{col_name}': '{0:,.0f}',
                f'Cumulative {col_name}': '{0:,.0f}'
            }
            return results.style.format(format_dict)
        else:
            return results

    def missing(self, clip_0=False, style=False):
        """ Build table of missing data in each column. 

            clip_0 (bool):     In cases where 0 counts are generated, remove them from the list
            style (bool):     Apply a pandas style to format percentages

        Returns:
            DataFrame with each Column including total Missing Values, Percent Missing 
            and Total rows
        """
        missing = pd.concat([self._obj.isna().sum(),
                             self._obj.isna().mean()],
                            axis='columns').rename(columns={
                                0: 'Missing',
                                1: 'Percent'
                            })
        missing['Total'] = len(self._obj)
        if clip_0:
            missing = missing[missing['Missing'] > 0]

        results = missing[['Missing', 'Total',
                           'Percent']].sort_values(by=['Missing'],
                                                   ascending=False)
        if style:
            format_dict = {'Percent': '{:.2%}', 'Total': '{0:,.0f}'}
            return results.style.format(format_dict)
        else:
            return results

    def _get_group_levels(self, level=1):
        """Internal helper function to flatten out the group list from a multiindex

        Args:
            level (int, optional): [description]. Defaults to 1.

        Returns:
            [type]: [description]
        """
        list_items = [col[0:level] for col in self._obj.index]
        results = []
        for x in list_items:
            if not x in results:
                results+=[x]
        return results

    def subtotal(self,
                 sub_level=None,
                 grand_label='Grand Total',
                 sub_label='subtotal',
                 show_separator=True):
        """ Add subtotals to a DataFrame. If the DataFrame has a multi-index, will
        add a subtotal at the lowest level as well as a Grand total

            sub_level (int):       Grouping level to calculate subtotal. Default is max available.
            grand_label (str):     Label override for the total of the entire DataFrame
            sub_label (str):       Label override for the sub total of the group
            show_separator (bool): Default is True to show subtotal levels separated by |

        Returns:
            DataFrame Grand Total and Sub Total
        """

        all_levels = self._obj.index.nlevels

        max_level = all_levels - 1

        # No value is specified, use the maximum
        if not sub_level:
            sub_level = max_level
        if sub_level > max_level:
            raise AttributeError(
                f'Maximum number of subtotal levels is {max_level}')

        grand_total_label = tuple([f'{grand_label}'] +
                                  [' ' for _ in range(1, all_levels)])

        # If this is not a multiindex, just add the grand total to the DataFrame
        if all_levels == 1:
            # No subtotals since no groups
            # Make sure the index is an object so we can append the subtotal without
            # Getting into Categorical issues
            self._obj.index = self._obj.index.astype('object')

            # If not multi-level, rename should not be a tuple
            # Add the Grand Total label at the end
            return self._obj.append(
                self._obj.sum(numeric_only=True).rename(grand_total_label[0]))

        # Remove any categorical indices
        self._obj.index = pd.MultiIndex.from_tuples(
            [n for i, n in enumerate(self._obj.index)],
            names=list(self._obj.index.names))
        
        output = []
        for cross_section in self._get_group_levels(sub_level):
            num_spaces = all_levels - len(cross_section)
            if show_separator:
                total_label = ' | '.join(cross_section) + f' {sub_label}'
            else:
                total_label = f'{sub_label}'
            if sub_level == 1:
                sub_total_label = [cross_section[0]] + [total_label] + [' '] * num_spaces
            else:    
                sub_total_label = list(cross_section[0:(
                    sub_level - 1)]) + [total_label] + [' '] * num_spaces
            section = self._obj.xs(cross_section, drop_level=False)
            subtotal = section.sum(numeric_only=True).rename(
                tuple(sub_total_label))
            output.append(section.append(subtotal))

        return pd.concat(output).append(
            self._obj.sum(numeric_only=True).rename(grand_total_label))